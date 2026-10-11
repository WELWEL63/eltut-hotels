from app import create_app
from extensions import db
from blueprints.public.booking_routes import _product_meta
from models.room import Room
from models.package import Package
from models.activity import Activity

app = create_app()
with app.app_context():
    # Hotel room
    room = db.session.get(Room, 1022)
    meta_h = _product_meta("hotel", room)
    print("HOTEL meta:")
    for k, v in meta_h.items():
        print(f"  {k}: {v!r}")

    print()
    # Package
    pkg = db.session.get(Package, 885)
    meta_p = _product_meta("package", pkg)
    print("PACKAGE meta:")
    for k, v in meta_p.items():
        print(f"  {k}: {v!r}")

    print()
    # Activity
    act = db.session.get(Activity, 513)
    meta_a = _product_meta("activity", act)
    print("ACTIVITY meta:")
    for k, v in meta_a.items():
        print(f"  {k}: {v!r}")
