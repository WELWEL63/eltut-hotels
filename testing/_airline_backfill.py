"""
_airline_backfill.py
────────────────────
1. Ensures required airlines exist in the master table.
2. Backfills Flight.airline_id by matching normalized airline_name.
3. Prints a report.
Idempotent — safe to re-run.
"""

from app import create_app
from extensions import db
from models import Airline, Flight
from sqlalchemy import select, func


# ─── Airlines to ensure exist ───
# Format: (name, slug, country, logo_url)
# logo_url can be None — you'll add later via admin.
AIRLINES_TO_ENSURE = [
    ("EasyJet",  "easyjet",  "United Kingdom", "/static/images/airlines/1deedf9b230ac1620304736d514b6ac1294db24c.png"),
    ("TUI",      "tui",      "Germany",        "/static/images/airlines/124167c04b4a165a0136bc53621bc5ed9a862f6d.jpg"),
    ("Wizz Air", "wizz-air", "Hungary",        None),
]


# ─── Name normalization for matching flight.airline_name → Airline ───
# Maps normalized flight airline_name → canonical Airline.name
FLIGHT_NAME_MAP = {
    "easyjet":  "EasyJet",
    "easy jet": "EasyJet",
    "tui":      "TUI",
    "wizzair":  "Wizz Air",
    "wizz air": "Wizz Air",
}


def normalize(name: str | None) -> str:
    if not name:
        return ""
    return name.strip().lower().replace(" ", "")


app = create_app()
with app.app_context():
    print("=" * 60)
    print("STEP 1 — Ensure airlines exist in master table")
    print("=" * 60)

    for name, slug, country, logo in AIRLINES_TO_ENSURE:
        existing = db.session.scalar(
            select(Airline).where(Airline.slug == slug)
        )
        if existing:
            # Update logo if we have one and it's missing
            if logo and not existing.logo_url:
                existing.logo_url = logo
                print(f"  [update] {name!r} — added missing logo")
            else:
                print(f"  [exists] {name!r} (id={existing.id})")
        else:
            a = Airline(name=name, slug=slug, country=country, logo_url=logo, is_active=True)
            db.session.add(a)
            db.session.flush()
            print(f"  [create] {name!r} (id={a.id})")

    db.session.commit()
    print()

    # Refresh airline lookup
    airlines = list(db.session.scalars(select(Airline)))
    print(f"Airlines now in master ({len(airlines)}):")
    for a in airlines:
        print(f"  id={a.id} name={a.name!r} slug={a.slug!r} logo={a.logo_url!r}")
    print()

    # Build lookup by normalized name
    by_normalized = {normalize(a.name): a for a in airlines}

    # ─── Backfill ───
    print("=" * 60)
    print("STEP 2 — Backfill Flight.airline_id")
    print("=" * 60)

    all_flights = list(db.session.scalars(select(Flight)))
    updated = 0
    skipped = 0
    unmapped = set()

    for f in all_flights:
        if f.airline_id is not None:
            skipped += 1
            continue

        raw = f.airline_name or ""
        canonical = FLIGHT_NAME_MAP.get(raw.strip().lower())
        if canonical:
            airline = next((a for a in airlines if a.name == canonical), None)
            if airline:
                f.airline_id = airline.id
                updated += 1
                continue

        # Fallback: try direct normalized match
        norm = normalize(raw)
        airline = by_normalized.get(norm)
        if airline:
            f.airline_id = airline.id
            updated += 1
        else:
            unmapped.add(raw)

    db.session.commit()

    print(f"  Updated : {updated} flights")
    print(f"  Skipped : {skipped} flights (already had airline_id)")
    if unmapped:
        print(f"  Unmapped airline_name values: {sorted(unmapped)}")
    else:
        print("  Unmapped airline_name values: none ✅")

    print()

    # ─── Verify ───
    print("=" * 60)
    print("STEP 3 — Verify")
    print("=" * 60)

    rows = db.session.execute(
        select(Flight.airline_id, func.count(Flight.id))
        .group_by(Flight.airline_id)
    ).all()
    print("Flights grouped by airline_id:")
    for aid, cnt in rows:
        airline = next((a for a in airlines if a.id == aid), None)
        label = f"{airline.name!r}" if airline else "(NULL — not linked)"
        print(f"  airline_id={aid} ({label}) -> {cnt} flights")

    print()
    print("=" * 60)
    print("DONE")
    print("=" * 60)
