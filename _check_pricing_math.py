from datetime import date
from app import create_app
from extensions import db
from blueprints.public.booking_routes import _room_stay_pricing
from models.room import Room

app = create_app()
with app.app_context():
    room = db.session.get(Room, 1022)
    print(f"Room: {room.id} {room.type!r}")
    print(f"  base_price_per_night: {room.base_price_per_night}")
    print(f"  max_occupancy: {room.max_occupancy}")
    print()
    pricing = _room_stay_pricing(
        room,
        date(2027, 1, 28),
        date(2027, 2, 4),
        2,
        2,
    )
    print("Pricing returned by _room_stay_pricing:")
    for k, v in pricing.items():
        print(f"  {k}: {v!r}")
