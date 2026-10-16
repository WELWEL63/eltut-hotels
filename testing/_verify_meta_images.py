from app import create_app
from extensions import db
from blueprints.public.booking_routes import _product_meta
from models.room import Room
from models.package import Package
from models.activity import Activity

app = create_app()
with app.app_context():
    print("HOTEL:")
    m = _product_meta("hotel", db.session.get(Room, 1022))
    print(f"  image={m.get('image')!r}")
    print(f"  destination={m.get('destination')!r}")

    print("\nPACKAGE:")
    m = _product_meta("package", db.session.get(Package, 885))
    print(f"  image={m.get('image')!r}")
    print(f"  destination={m.get('destination')!r}")

    print("\nACTIVITY:")
    m = _product_meta("activity", db.session.get(Activity, 513))
    print(f"  image={m.get('image')!r}")
