from app import create_app
from extensions import db
from models import Room, Hotel
app = create_app()
ctx = app.app_context()
ctx.push()
r = db.session.get(Room, 1233)  # from the URL earlier
print("room:", r.id, r.type, "meal=", r.meal_plan, "max_occ=", r.max_occupancy)
h = db.session.get(Hotel, r.hotel_id)
print("hotel:", h.name, "stars=", h.stars, "addr=", h.address, "dest=", h.destination_id)
ctx.pop()