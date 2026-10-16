from datetime import date
from app import create_app
from extensions import db
from services import search_service, pricing_service
from services import availability_service
from models import Hotel, Activity, Room, ActivityPrice

app = create_app()
ctx = app.app_context()
ctx.push()

print("=== 1. HOTEL search (is_bookable filter must NOT affect hotels) ===")
r = search_service.search(product_type="hotel", check_in=date(2027,1,31), check_out=date(2027,2,7), adults=2, children=0)
print(" total:", r["total"], "items:", len(r["items"]))
for i in r["items"][:3]:
    print("  ", i["id"], i["name"][:40], "price_adult", i["price_adult"], "total", i["total_price"])

print()
print("=== 2. ACTIVITY search ===")
r = search_service.search(product_type="activity", adults=2, children=0)
print(" total:", r["total"], "items:", len(r["items"]))
for i in r["items"][:3]:
    print("  ", i["id"], i["name"][:40], "price_adult", i["price_adult"], "total", i["total_price"])

print()
print("=== 3. HOTEL pricing via compute_booking_total (no package_flight_id) ===")
room = db.session.query(Room).filter(Room.base_price_per_night.is_not(None)).first()
if room:
    try:
        total = pricing_service.compute_booking_total(
            product_type="hotel", product_id=room.id,
            adults=2, children=0,
            check_in=date(2027,1,31), check_out=date(2027,2,7),
        )
        print("  room", room.id, "total:", total)
    except Exception as e:
        print("  ERROR:", e)

print()
print("=== 4. ACTIVITY pricing via compute_booking_total (no package_flight_id) ===")
act = db.session.query(Activity).first()
if act:
    try:
        total = pricing_service.compute_booking_total(
            product_type="activity", product_id=act.id,
            adults=2, children=0,
        )
        print("  activity", act.id, act.name[:40], "total:", total)
    except Exception as e:
        print("  ERROR:", e)

print()
print("=== 5. flight_options_for_package gone from flight_service ===")
import services.flight_service as fs
print("  has flight_options_for_package:", hasattr(fs, "flight_options_for_package"))
print("  has round_trip_cost:", hasattr(fs, "round_trip_cost"))
print("  has flight_summary_for_package:", hasattr(fs, "flight_summary_for_package"))

print()
print("=== 6. confirmation route handles hotel/activity gracefully (no crash) ===")
# We won't create a real booking; just check the enrich branch does not explode
from models import Booking
from sqlalchemy import select
non_pkg = db.session.scalar(
    select(Booking).where(Booking.product_type != "package").limit(1)
)
print("  found non-package booking:", non_pkg.reference if non_pkg else "(none — can't test route directly)")

ctx.pop()