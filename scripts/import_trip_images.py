"""
scripts/import_trip_images.py
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
Bulk-import trip gallery images into the ActivityImage table.

SOURCE FOLDER
    C:\Users\washo\Desktop\Software Eng\eltuttours\frontend\public\Trips\
    (override with --src)

NAMING CONVENTION
    TRIP{n}.ext        -> nth activity (by id ASC), sort_order = 0
    TRIP{n}_{k}.ext    -> nth activity, sort_order = k

    Files NOT matching TRIP\d+(_\d+)?\.(jpg|jpeg|png|webp|gif) are ignored
    (e.g. Tripadvisor--2023.jpg, WinterSun.jpg, UNKNOWN_1.jpg).

STORAGE
    Bytes are SHA-1'd and written to
        static/images/activities/<sha1>.<ext>
    Duplicate content = one file on disk.

DB
    ActivityImage(activity_id, url, sort_order, media_type='image')
    Idempotent: skips rows where (activity_id, sort_order) already exists.

USAGE
    python scripts/import_trip_images.py --dry-run    # preview
    python scripts/import_trip_images.py              # for real
    python scripts/import_trip_images.py --src "C:\other\path"
"""

from __future__ import annotations

import argparse
import hashlib
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app import create_app                          # noqa: E402
from extensions import db                           # noqa: E402
from models import Activity, ActivityImage                  # noqa: E402


DEFAULT_SRC = Path(
    r"C:\Users\washo\Desktop\Software Eng\eltuttours\frontend\public\Trips"
)

NAME_RE = re.compile(
    r"^TRIP(\d+)(?:_(\d+))?\s*\.(jpg|jpeg|png|webp|gif)$",
    re.IGNORECASE,
)

VALID_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
MAX_BYTES = 25 * 1024 * 1024  # 25 MB safety cap


def parse_filename(name: str) -> tuple[int, int] | None:
    """Return (trip_seq, position) or None if the name doesn't match."""
    m = NAME_RE.match(name.strip())
    if not m:
        return None
    trip_seq = int(m.group(1))
    pos = int(m.group(2)) if m.group(2) is not None else 0
    ext = "." + m.group(3).lower()
    if ext not in VALID_EXTS:
        return None
    return trip_seq, pos


def images_dir() -> Path:
    d = ROOT / "static" / "images" / "activities"
    d.mkdir(parents=True, exist_ok=True)
    return d


def sha1_bytes(data: bytes) -> str:
    return hashlib.sha1(data).hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description="Import TRIP* images into ActivityImage.")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC,
                    help=f"Source folder (default: {DEFAULT_SRC})")
    ap.add_argument("--dry-run", action="store_true",
                    help="Print plan only - no disk writes, no DB changes.")
    args = ap.parse_args()

    if not args.src.is_dir():
        print(f"ERROR: source folder not found: {args.src}")
        return 2

    app = create_app()
    with app.app_context():
        activities = (
            db.session.query(Activity)
            .order_by(Activity.id.asc())
            .all()
        )
        print(f"Found {len(activities)} activities "
              f"(id {activities[0].id} ... {activities[-1].id})")

        existing = {
            (row.activity_id, row.sort_order)
            for row in db.session.query(ActivityImage).all()
        }
        print(f"Existing ActivityImage rows: {len(existing)}")

        files = sorted(p for p in args.src.iterdir() if p.is_file())
        print(f"Source files: {len(files)}")
        print(f"Target images dir: {images_dir()}")

        stats = {
            "imported": 0,
            "skipped_exists": 0,
            "skipped_dup_file": 0,
            "skipped_orphan": 0,
            "skipped_no_activity": 0,
            "skipped_too_big": 0,
            "errors": 0,
        }

        plan = []

        for f in files:
            parsed = parse_filename(f.name)
            if parsed is None:
                stats["skipped_orphan"] += 1
                continue
            trip_seq, pos = parsed

            if trip_seq < 1 or trip_seq > len(activities):
                stats["skipped_no_activity"] += 1
                print(f"  [NO-ACT] {f.name} (TRIP{trip_seq:03d} > {len(activities)})")
                continue

            activity = activities[trip_seq - 1]
            key = (activity.id, pos)
            if key in existing:
                stats["skipped_exists"] += 1
                continue

            try:
                size = f.stat().st_size
            except OSError as exc:
                print(f"  [ERR]   {f.name}: {exc}")
                stats["errors"] += 1
                continue

            if size > MAX_BYTES:
                print(f"  [BIG]   {f.name} ({size / 1024 / 1024:.1f} MB) - skipped")
                stats["skipped_too_big"] += 1
                continue

            plan.append((f, activity.id, pos, activity.slug))

        if args.dry_run:
            print()
            print(f"DRY-RUN: would import {len(plan)} file(s)")
            print(f"  Skipped (already in DN):  {stats['skipped_exists']}")
            print(f"  Skipped (no activity):    {stats['skipped_no_activity']}")
            print(f"  Skipped (orphan name):    {stats['skipped_orphan']}")
            print(f"  Skipped (too big >25MB):  {stats['skipped_too_big']}")
            print(f"  Errors:                   {stats['errors']}")
            print()
            print("First 10 planned rows:")
            for src, act_id, pos, slug in plan[:10]:
                print(f"  {src.name:24s} -> activity {act_id} ({slug}), sort={pos}")
            print()
            print("R-run without --dry-run to apply.")
            return 0

        target_dir = images_dir()

        try:
            for src, act_id, pos, slug in plan:
                data = src.read_bytes()
                digest = sha1_bytes(data)
                ext = src.suffix.lower()
                fname = f"{digest}{ext}"
                target = target_dir / fname

                if target.exists():
                    stats["skipped_dup_file"] += 1
                else:
                    target.write_bytes(data)

                url = f"/static/images/activities/{fname}"
                db.session.add(ActivityImage(
                    activity_id=act_id,
                    url=url,
                    sort_order=pos,
                    media_type="image",
                ))
                stats["imported"] += 1
                print(f"  [OK]    {src.name:24s} -> {url} (activity {act_id})")

            db.session.commit()
        except Exception as exc:
            db.session.rollback()
            print(f"ERROR during write - rolled back: {exc}")
            return 1

        print()
        print("=" * 60)
        print("IMPORT COMPLETE")
        print("=" * 60)
        print(f"  Imported:              {stats['imported']}")
        print(f"  Skipped (already DB):  {stats['skipped_exists']}")
        print(f"  Skipped (dup file):    {stats['skipped_dup_file']}")
        print(f"  Skipped (no activity): {stats['skipped_no_activity']}")
        print(f"  Skipped (orphan name): {stats['skipped_orphan']}")
        print(f"  Skipped (too big):     {stats['skipped_too_big']}")
        print(f"  Errors:                {stats['errors']}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
