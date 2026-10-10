from app import create_app
from extensions import db
from models import Flight, Airline, PackageOption

app = create_app()
with app.app_context():
    print("=" * 50)
    print("AIRLINES:")
    for a in db.session.query(Airline).all():
        print(f"  id={a.id} name={a.name!r} logo={a.logo_url!r}")

    print()
    print("=" * 50)
    print("FLIGHTS:")
    for f in db.session.query(Flight).limit(10).all():
        aid = getattr(f, "airline_id", None)
        print(f"  id={f.id} package_id={f.package_id} airline_id={aid} airline_name={f.airline_name!r}")

    print()
    print("=" * 50)
    print("PACKAGE 885 OPTIONS:")
    opts = db.session.query(PackageOption).filter_by(package_id=885).all()
    print(f"  count={len(opts)}")
    for o in opts:
        print(f"  id={o.id} flight_id={o.flight_id} price_id={o.price_id} label={o.label!r}")

    print()
    print("=" * 50)
    print("ALL OPTIONS IN DB (any package):")
    all_opts = db.session.query(PackageOption).limit(10).all()
    print(f"  total (first 10): {len(all_opts)}")
    for o in all_opts:
        print(f"  id={o.id} package_id={o.package_id} flight_id={o.flight_id} price_id={o.price_id}")

    print()
    print("=" * 50)
    print("ALL FLIGHTS IN DB (any package):")
    all_f = db.session.query(Flight).limit(10).all()
    print(f"  total (first 10): {len(all_f)}")
    for f in all_f:
        print(f"  id={f.id} package_id={f.package_id} airline_id={getattr(f, 'airline_id', None)} airline_name={f.airline_name!r}")
