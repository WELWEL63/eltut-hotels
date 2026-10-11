"""
scripts/enrich_activity_maps.py
───────────────────────────────
Populate Activity.google_maps_url for every activity.

Builds a Google Maps *embed* URL from the activity's destination
coordinates. If the destination has no coords in our map, uses
the activity name + destination as a query.

Idempotent: skips activities that already have a URL.

USAGE
    python scripts/enrich_activity_maps.py --dry-run
    python scripts/enrich_activity_maps.py
    python scripts/enrich_activity_maps.py --force
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import quote_plus

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app  # noqa: E402
from extensions import db  # noqa: E402
from models import Activity, Destination  # noqa: E402


# Destination centre coordinates (same as enrich_hotels.py)
DEST_COORDS: dict[str, tuple[float, float]] = {
    "hurghada":      (27.2579, 33.8116),
    "sharm":         (27.9158, 34.3299),
    "luxor":         (25.6872, 32.6396),
    "aswan":         (24.0889, 32.8998),
    "cairo":         (30.0444, 31.2357),
    "dahab":         (28.5094, 34.5135),
    "taba":          (29.4928, 34.8962),
    "nile":          (25.6872, 32.6396),
    "marsa":         (25.0667, 34.9000),
    "el gouna":      (27.3950, 33.6780),
    "soma bay":      (26.8470, 33.9880),
    "makadi":        (26.9940, 33.9080),
    "nuweiba":       (29.0333, 34.6667),
    "tiran":         (27.9500, 34.4000),
    "naama":         (27.9120, 34.3300),
    "sahl hasheesh": (27.0460, 33.8800),
    "port ghalib":   (25.5333, 34.6333),
    "portghalib":    (25.5333, 34.6333),
}


def _dest_key(name: str) -> str:
    n = (name or "").strip().lower()
    for key in DEST_COORDS:
        if key in n:
            return key
    return "hurghada"


def _embed_url(activity_name: str, dest_name: str) -> str:
    """Build a Google Maps embed URL for the activity."""
    key = _dest_key(dest_name)
    lat, lng = DEST_COORDS.get(key, DEST_COORDS["hurghada"])
    # Use destination centre + activity name for a specific pin
    q = quote_plus(f"{activity_name} {dest_name}")
    return f"https://www.google.com/maps?q={q}&center={lat},{lng}&z=12&output=embed"


def enrich(dry_run: bool, force: bool) -> int:
    app = create_app()
    with app.app_context():
        activities = db.session.query(Activity).order_by(Activity.id).all()
        destinations = {d.id: d.name for d in db.session.query(Destination).all()}

        added = 0
        skipped = 0

        for a in activities:
            if not force and a.google_maps_url:
                skipped += 1
                continue

            dest_name = destinations.get(a.destination_id, "Egypt")
            url = _embed_url(a.name or "Activity", dest_name)

            if not dry_run:
                a.google_maps_url = url
            added += 1
            print(f"  {a.id:4d} | {a.name[:45]:45s} | {dest_name[:20]}")

        if not dry_run:
            db.session.commit()
            print("\n=== COMMITTED ===")
        else:
            print("\n=== DRY RUN (nothing committed) ===")

        print(f"URLs added:   {added}")
        print(f"Skipped:      {skipped} (already had URL)")
        return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    return enrich(dry_run=args.dry_run, force=args.force)


if __name__ == "__main__":
    raise SystemExit(main())