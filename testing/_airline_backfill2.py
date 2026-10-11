"""_airline_backfill2.py - Defensive backfill with progress + error handling."""
from app import create_app
from extensions import db
from models import Airline, Flight
from sqlalchemy import select


FLIGHT_NAME_MAP = {
    "easyjet":  "easyjet",     # master name is lowercase 'easyjet'
    "easy jet": "easyjet",
    "tui":      "TUI",
    "wizzair":  "Wizz Air",
    "wizz air": "Wizz Air",
}


app = create_app()
with app.app_context():
    # Load airlines
    airlines = list(db.session.scalars(select(Airline)))
    print(f"Airlines loaded: {len(airlines)}")
    for a in airlines:
        print(f"  id={a.id} name={a.name!r}")
    print()

    # Build name -> airline map
    by_name = {}
    for a in airlines:
        if a.name:
            by_name[a.name.strip().lower().replace(" ", "")] = a

    # Process all flights
    print("Loading flights...")
    flights = list(db.session.scalars(select(Flight)))
    print(f"  Loaded {len(flights)} flights")
    print()

    updated = 0
    skipped = 0
    unmapped = {}

    for i, f in enumerate(flights, 1):
        if f.airline_id is not None:
            skipped += 1
            continue

        raw = (f.airline_name or "").strip()
        canonical = FLIGHT_NAME_MAP.get(raw.lower())

        airline = None
        if canonical:
            airline = by_name.get(canonical.strip().lower().replace(" ", ""))
        if airline is None:
            norm = raw.lower().replace(" ", "")
            airline = by_name.get(norm)

        if airline:
            f.airline_id = airline.id
            updated += 1
        else:
            unmapped[raw] = unmapped.get(raw, 0) + 1

        # Progress + batch commit
        if i % 200 == 0:
            db.session.commit()
            print(f"  Progress: {i}/{len(flights)} — updated={updated} skipped={skipped}")

    db.session.commit()

    print()
    print("=" * 50)
    print(f"Updated : {updated}")
    print(f"Skipped : {skipped} (already had airline_id)")
    print(f"Unmapped: {unmapped if unmapped else 'none'}")
    print("=" * 50)
