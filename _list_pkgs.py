from app import create_app
from extensions import db
from models import Package, Hotel, Room, Destination, PackagePrice

app = create_app()
with app.app_context():
    rows = db.session.query(
        Package.id, Package.code, Package.name,
        Package.hotel_id, Package.room_id,
        Package.duration_nights, Package.is_active
    ).order_by(Package.id).all()
    for r in rows:
        code = r.code or '-'
        name = (r.name or '')[:45]
        print(f'id={r.id:>4}  {code:<12}  {name:<45}  h={r.hotel_id}  r={r.room_id}  {r.duration_nights}n  active={r.is_active}')

    print()
    print('--- Reference counts ---')
    print('Packages:      ', db.session.query(Package.id).count())
    print('PackagePrices: ', db.session.query(PackagePrice.id).count())
    print('Hotels:        ', db.session.query(Hotel.id).count())
    print('Rooms:         ', db.session.query(Room.id).count())
    print('Destinations:  ', db.session.query(Destination.id).count())

    print()
    print('--- Price windows for first package ---')
    first_pkg = rows[0] if rows else None
    if first_pkg:
        prices = db.session.query(PackagePrice).filter_by(package_id=first_pkg.id).order_by(PackagePrice.valid_from).limit(10).all()
        for p in prices:
            print(f'  {p.valid_from} -> {p.valid_to}  {p.currency} {p.adult_price}')