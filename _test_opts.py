from app import create_app
from extensions import db
from models import Package
from services.flight_service import flight_options_for_package
from datetime import date

app = create_app()
ctx = app.app_context()
ctx.push()

print("=" * 60)
print("TEST 1 — Hurghada 2026-11-01 (should show 11-01, offset=0)")
print("=" * 60)

pkg = db.session.query(Package).filter(Package.destination_id == 27).first()
opts = flight_options_for_package(
    package=pkg,
    check_in=date(2026, 11, 1),
    check_out=date(2026, 11, 8),
    passengers=2,
    land_total=840.00,
)
print(f"{len(opts)} options:")
for o in opts:
    print(f"  {o['airline_name']:<10} {o['departure_date']} offset={o['offset_days']:+d}  grand_total={o['grand_total']}")

print()
print("=" * 60)
print("TEST 2 — Gap date 2027-07-02 (should offset to nearest)")
print("=" * 60)

opts2 = flight_options_for_package(
    package=pkg,
    check_in=date(2027, 7, 2),
    check_out=date(2027, 7, 9),
    passengers=2,
    land_total=840.00,
)
print(f"{len(opts2)} options:")
for o in opts2:
    print(f"  {o['airline_name']:<10} {o['departure_date']} offset={o['offset_days']:+d}  grand_total={o['grand_total']}")