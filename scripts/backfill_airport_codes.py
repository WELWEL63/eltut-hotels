"""
scripts/backfill_airport_codes.py
─────────────────────────────────
Populate Destination.airport_code for the 16 known destinations.

Idempotent: re-running updates in place, never duplicates.
"""

from __future__ import annotations

import sys

from app import create_app
from extensions import db
from models import Destination

MAPPING: dict[str, str | None] = {
    "Aswan":            "ASW",
    "Cairo":            "CAI",
    "Dahab":            "SSH",
    "El Gouna":         "HRG",
    "Hurghada":         "HRG",
    "Luxor":            "LXR",
    "Makadi Bay":       "HRG",
    "Marsa Alam":       "RMF",
    "Nile Cruise":      None,
    "Portghalib":       "RMF",
    "Safaga":           "HRG",
    "Sahl Hasheesh":    "HRG",
    "Sharm El Sheikh":  "SSH",
    "Soma Bay":         "HRG",
    "Taba":             "TCP",
    "Transfer":         None,
}


def main() -> int:
    app = create_app()
    with app.app_context():
        updated = 0
        unchanged = 0
        missing = []

        for name, code in MAPPING.items():
            dest = db.session.query(Destination).filter_by(name=name).first()
            if dest is None:
                missing.append(name)
                continue

            if dest.airport_code == code:
                unchanged += 1
                continue

            dest.airport_code = code
            updated += 1
            print(f"  {name:<20} -> {code}")

        db.session.commit()

        print()
        print(f"Updated:   {updated}")
        print(f"Unchanged: {unchanged}")
        if missing:
            print(f"Missing (not found in DB): {missing}")

        print()
        print("Final state:")
        for d in db.session.query(Destination).order_by(Destination.name).all():
            print(f"  id={d.id:<4} {d.name:<20} airport_code={d.airport_code}")

    return 0


if __name__ == "__main__":
    sys.exit(main())