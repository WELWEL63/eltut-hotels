"""_seed_package_options.py - Create 3 test flight options for package 885."""
from datetime import date
from decimal import Decimal

from app import create_app
from extensions import db
from models import Flight, Package, PackagePrice, PackageOption, Airline
from sqlalchemy import select


PACKAGE_ID = 885
DEPARTURE_DATE = date(2027, 1, 28)
RETURN_DATE = date(2027, 2, 4)


SEED_OPTIONS = [
    {"airline_slug": "easyjet",  "from": "Manchester", "to": "Hurghada",
     "luggage": "23kg", "adult": Decimal("888.00"),  "child": Decimal("650.00"),
     "label": "EasyJet - Manchester to Hurghada"},
    {"airline_slug": "tui",      "from": "Manchester", "to": "Hurghada",
     "luggage": "25kg", "adult": Decimal("989.00"),  "child": Decimal("720.00"),
     "label": "TUI - Manchester to Hurghada"},
    {"airline_slug": "wizz-air", "from": "Manchester", "to": "Hurghada",
     "luggage": "20kg", "adult": Decimal("1050.00"), "child": Decimal("780.00"),
     "label": "Wizz Air - Manchester to Hurghada"},
]


app = create_app()
with app.app_context():
    pkg = db.session.get(Package, PACKAGE_ID)
    if not pkg:
        print(f"Package {PACKAGE_ID} not found")
        raise SystemExit(1)

    print(f"Package: {pkg.id} {pkg.name!r}")
    print(f"  room_id: {pkg.room_id}")
    print(f"  duration: {pkg.duration_nights} nights")
    print()

    created = 0
    skipped = 0

    for spec in SEED_OPTIONS:
        airline = db.session.scalar(
            select(Airline).where(Airline.slug == spec["airline_slug"])
        )
        if not airline:
            print(f"Airline not found: {spec['airline_slug']}")
            continue

        existing_opt = db.session.scalar(
            select(PackageOption).where(
                PackageOption.package_id == PACKAGE_ID,
                PackageOption.label == spec["label"],
            )
        )
        if existing_opt:
            print(f"  [skip] {spec['label']!r} already exists (id={existing_opt.id})")
            skipped += 1
            continue

        flight = db.session.scalar(
            select(Flight).where(
                Flight.package_id == PACKAGE_ID,
                Flight.airline_id == airline.id,
            ).limit(1)
        )
        if flight is None:
            flight = Flight(
                package_id=PACKAGE_ID,
                airline_id=airline.id,
                flight_from=spec["from"],
                flight_to=spec["to"],
                airline_name=airline.name,
                luggage_allowance=spec["luggage"],
                included=True,
                is_active=True,
            )
            db.session.add(flight)
            db.session.flush()
            print(f"  [flight] created id={flight.id} for {airline.name}")
        else:
            print(f"  [flight] reusing id={flight.id} for {airline.name}")

        price = PackagePrice(
            package_id=PACKAGE_ID,
            adult_price=spec["adult"],
            child_price=spec["child"],
            currency="EUR",
        )
        db.session.add(price)
        db.session.flush()
        print(f"  [price ] created id={price.id} - {spec['adult']} / {spec['child']} EUR")

        option = PackageOption(
            package_id=PACKAGE_ID,
            flight_id=flight.id,
            price_id=price.id,
            room_id=pkg.room_id,
            departure_date=DEPARTURE_DATE,
            return_date=RETURN_DATE,
            label=spec["label"],
            is_active=True,
            sort_order=int(spec["adult"]),
        )
        db.session.add(option)
        db.session.flush()
        print(f"  [option] created id={option.id} - {spec['label']!r}")
        print()
        created += 1

    db.session.commit()

    print("=" * 60)
    print(f"Created: {created}  |  Skipped: {skipped}")
    print("=" * 60)
    print()

    options = list(db.session.scalars(
        select(PackageOption).where(PackageOption.package_id == PACKAGE_ID)
        .order_by(PackageOption.sort_order)
    ))
    print(f"Package {PACKAGE_ID} options ({len(options)}):")
    for o in options:
        flight = o.flight
        price = o.price
        print(f"  id={o.id} label={o.label!r}")
        if flight:
            print(f"    flight: {flight.airline_name} ({flight.flight_from} -> {flight.flight_to})")
        if price:
            print(f"    price : {price.adult_price} / {price.child_price} {price.currency}")
