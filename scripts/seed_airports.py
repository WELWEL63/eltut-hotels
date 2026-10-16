"""
scripts/seed_airports.py
────────────────────────
Load data/airports.csv into the airports table.

Idempotent: re-running updates existing rows (by iata_code), never duplicates.
"""

from __future__ import annotations

import csv
import sys
from pathlib import Path

from app import create_app
from extensions import db
from models import Airport


CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "airports.csv"


def main() -> int:
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found")
        return 2

    app = create_app()
    with app.app_context():
        inserted = 0
        updated = 0

        with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                code = (row.get("iata_code") or "").strip().upper()
                if not code:
                    continue

                existing = db.session.get(Airport, code)
                if existing is None:
                    db.session.add(Airport(
                        iata_code=code,
                        name=(row.get("name") or "").strip(),
                        city=(row.get("city") or "").strip() or None,
                        country=(row.get("country") or "").strip() or None,
                    ))
                    inserted += 1
                else:
                    existing.name = (row.get("name") or "").strip()
                    existing.city = (row.get("city") or "").strip() or None
                    existing.country = (row.get("country") or "").strip() or None
                    updated += 1

        db.session.commit()

        total = db.session.query(Airport).count()
        print(f"Inserted: {inserted}")
        print(f"Updated:  {updated}")
        print(f"Total:    {total}")

    return 0


if __name__ == "__main__":
    sys.exit(main())