from app import create_app
from extensions import db
from models import Flight, PackageOption, Package, Airline
from sqlalchemy import select

app = create_app()
with app.app_context():
    pkg = db.session.get(Package, 885)
    if not pkg:
        print("Package 885 not found")
        raise SystemExit(1)

    print(f"PACKAGE: {pkg.id} {pkg.name!r}")
    print()

    flights = list(db.session.scalars(
        select(Flight).where(Flight.package_id == pkg.id)
    ))
    print(f"FLIGHTS attached to package ({len(flights)}):")
    for f in flights:
        print(f"  id={f.id} {f.flight_from} -> {f.flight_to}")
        print(f"    airline_name={f.airline_name!r}")
        print(f"    luggage={f.luggage_allowance!r}")
        print(f"    included={f.included}")
        print(f"    is_active={f.is_active}")
    print()

    options = list(db.session.scalars(
        select(PackageOption).where(PackageOption.package_id == pkg.id)
    ))
    print(f"PACKAGE OPTIONS ({len(options)}):")
    for opt in options:
        flight = opt.flight
        print(f"  id={opt.id} label={opt.display_label!r}")
        print(f"    flight_id={opt.flight_id}")
        if flight:
            print(f"    flight: {flight.flight_from} -> {flight.flight_to}")
            print(f"    airline_name={flight.airline_name!r}")
        else:
            print(f"    NO FLIGHT (land only)")
        print(f"    price_id={opt.price_id} room_id={opt.room_id}")
        print(f"    departure={opt.departure_date} return={opt.return_date}")
    print()

    airlines = list(db.session.scalars(select(Airline)))
    print(f"AIRLINES in system ({len(airlines)}):")
    for a in airlines[:8]:
        print(f"  id={a.id} name={a.name!r} logo_url={a.logo_url!r}")
    print()

    print("MATCH: flight.airline_name vs airlines.name")
    airline_names = {a.name.strip().lower() for a in airlines if a.name}
    for f in flights:
        if f.airline_name:
            match = f.airline_name.strip().lower() in airline_names
            print(f"  {f.airline_name!r} -> match={match}")
    print()

    print("=" * 60)
    print("Flight columns:", [c.name for c in Flight.__table__.columns])
    print("PackageOption columns:", [c.name for c in PackageOption.__table__.columns])
    print("Airline columns:", [c.name for c in Airline.__table__.columns])
