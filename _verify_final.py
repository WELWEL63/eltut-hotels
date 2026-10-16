from app import create_app
from extensions import db
from models import Package, PackagePrice, FlightPrice
from sqlalchemy import select
from datetime import date

app = create_app()
ctx = app.app_context()
ctx.push()

slug = "hurghada-iberotel-club-fanar-standard-room-pool-garden-view"
pkg = db.session.scalar(select(Package).where(Package.slug == slug))

check_in = date(2027, 1, 15)
check_out = date(2027, 1, 22)
nights = (check_out - check_in).days

print("=" * 60)
print(f"USER: {check_in} -> {check_out}  ({nights} nights, 2 adults)")
print("=" * 60)
print()

# All windows covering 15 Jan
print("Windows covering 2027-01-15:")
candidates = []
for pr in db.session.scalars(
    select(PackagePrice)
    .where(
        PackagePrice.package_id == pkg.id,
        PackagePrice.valid_from <= check_in,
        PackagePrice.valid_to >= check_in,
    )
    .order_by(PackagePrice.adult_price)
).all():
    wn = (pr.valid_to - pr.valid_from).days
    candidates.append(pr)
    nightly = float(pr.adult_price) / wn
    print(f"  {pr.valid_from} -> {pr.valid_to}  ({wn}n)  EUR {pr.adult_price}  →  EUR {nightly:.2f}/night")

if not candidates:
    print("  NONE")
    exit(0)
print()

# Tightest window
tightest = min(candidates, key=lambda pr: (pr.valid_to - pr.valid_from).days)
w_nights = (tightest.valid_to - tightest.valid_from).days
nightly = float(tightest.adult_price) / w_nights

print(f"Tightest window: {tightest.valid_from} -> {tightest.valid_to}")
print(f"  Nights: {w_nights}")
print(f"  Window total: EUR {tightest.adult_price}")
print(f"  Nightly rate: EUR {nightly:.2f}/adult")
print()

land = nightly * nights * 2
print(f"Land cost: {nightly:.2f} × {nights} × 2 = EUR {land:.2f}")
print()

# Flights
flights = db.session.scalars(
    select(FlightPrice).where(
        FlightPrice.origin == "LGW",
        FlightPrice.destination == "HRG",
        FlightPrice.direction == "out",
        FlightPrice.departure_date == check_in,
    )
).all()
print("Flights on 2027-01-15:")
for f in flights:
    print(f"  {f.airline} GBP {f.price_gbp}")
if flights:
    flight_price = float(flights[0].price_gbp)
    flight_total = flight_price * 2 * 2
    print(f"  Flight total: {flight_price} × 2 legs × 2 pax = GBP {flight_total:.2f}")
    markup = flight_total * 0.125
    transfer = 40 + 10
    print(f"  Markup: {markup:.2f}")
    print(f"  Transfer: {transfer:.2f}")
    grand = land + flight_total + markup + transfer
    print()
    print(f"GRAND TOTAL: {land:.2f} + {flight_total:.2f} + {markup:.2f} + {transfer:.2f} = {grand:.2f}")