from app import create_app
from extensions import db
from models import Package, Hotel, Room, Destination, FlightPrice
from sqlalchemy import select
from datetime import date

app = create_app()
ctx = app.app_context()
ctx.push()

slug = "hurghada-iberotel-club-fanar-standard-room-pool-garden-view"

pkg = db.session.scalar(select(Package).where(Package.slug == slug))
print("=" * 60)
print("PACKAGE:", pkg.name)
print("=" * 60)
print(f"  duration_nights: {pkg.duration_nights}")
print(f"  hotel_id: {pkg.hotel_id}  room_id: {pkg.room_id}  dest_id: {pkg.destination_id}")
print()

hotel = db.session.get(Hotel, pkg.hotel_id)
print("HOTEL:")
print(f"  name:         {hotel.name}")
print(f"  stars:        {hotel.stars}")
print(f"  destination:  {hotel.destination_id}")
print()

room = db.session.get(Room, pkg.room_id)
print("ROOM:")
print(f"  type:         {room.type}")
print(f"  meal_plan:    {room.meal_plan}")
print(f"  max_occupancy:{room.max_occupancy}")
print(f"  capacity:     {room.capacity}")
print(f"  base_price:   {room.base_price_per_night}")
print()

dest = db.session.get(Destination, pkg.destination_id)
print("DESTINATION:")
print(f"  name:         {dest.name}")
print(f"  airport_code: {dest.airport_code}")
print()

print("=" * 60)
print("FLIGHTS LGW -> HRG near 2027-01-15")
print("=" * 60)

flights = db.session.scalars(
    select(FlightPrice)
    .where(
        FlightPrice.origin == "LGW",
        FlightPrice.destination == "HRG",
        FlightPrice.direction == "out",
        FlightPrice.departure_date >= date(2027, 1, 12),
        FlightPrice.departure_date <= date(2027, 1, 18),
    )
    .order_by(FlightPrice.departure_date)
).all()

for f in flights:
    print(f"  {f.departure_date}  {f.airline:<10}  GBP {f.price_gbp}")
print()

print("=" * 60)
print("PRICE WINDOWS FOR THIS PACKAGE")
print("=" * 60)
from models import PackagePrice
prices = db.session.scalars(
    select(PackagePrice)
    .where(PackagePrice.package_id == pkg.id)
    .order_by(PackagePrice.valid_from)
    .limit(10)
).all()
for p in prices:
    print(f"  {p.valid_from} -> {p.valid_to}  {p.currency} {p.adult_price} adult / {p.child_price} child")

print()
print("=" * 60)
print("ROOM RATES FOR THIS ROOM")
print("=" * 60)
from models import RoomRate
rates = db.session.scalars(
    select(RoomRate)
    .where(RoomRate.room_id == room.id)
    .order_by(RoomRate.valid_from)
    .limit(10)
).all()
for r in rates:
    print(f"  {r.valid_from} -> {r.valid_to}  {r.currency} adult={r.adult_price} child={r.child_price}")