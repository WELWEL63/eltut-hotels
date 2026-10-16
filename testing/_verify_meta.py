from app import create_app
from blueprints.public.booking_routes import _product_meta
from extensions import db
from models.room import Room

app = create_app()
with app.app_context():
    room = db.session.get(Room, 1022)
    meta = _product_meta("hotel", room)
    print("meta keys:", sorted(meta.keys()))
    for k in ("name", "hotel", "room", "destination", "currency"):
        print(f"  {k} = {meta.get(k)!r}")
