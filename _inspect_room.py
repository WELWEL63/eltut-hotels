from app import create_app
from extensions import db
from models import Room, Hotel
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()
r = db.session.get(Room, 1178)
print("room 1178:", r)
if r:
    print("  type:", r.type, "meal_plan:", r.meal_plan, "hotel_id:", r.hotel_id, "max_occupancy:", r.max_occupancy)
    h = db.session.get(Hotel, r.hotel_id)
    if h:
        print("  hotel:", h.id, h.name, "stars:", h.stars, "dest_id:", h.destination_id)
        from models import HotelImage
        imgs = list(db.session.scalars(select(HotelImage).where(HotelImage.hotel_id == h.id).limit(3)))
        print("  hotel images:", [(i.url[:60], i.type) for i in imgs])
ctx.pop()