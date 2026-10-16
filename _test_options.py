from datetime import date
from app import create_app
from extensions import db
from models import Package
from services.package_options_service import options_for_package, cheapest_option_for_package

app = create_app()
ctx = app.app_context()
ctx.push()

p = db.session.get(Package, 919)
print("Package 919 | check_in=2027-01-31 check_out=2027-02-12 adults=2 children=0")
opts = options_for_package(p, date(2027,1,31), date(2027,2,12), adults=2, children=0)
print("option count:", len(opts))
for o in opts:
    print(" ", o["id"], o["airline_name"], o["departure_date"], "->", o["return_date"],
          "nights", o["nights"], "per_person", o["price_adult"], "grand", o["grand_total"],
          "offset", o["offset_days"])
cheap = cheapest_option_for_package(p, date(2027,1,31), date(2027,2,12), adults=2, children=0)
print("cheapest:", cheap and (cheap["id"], cheap["grand_total"]))
print()
print("Test tol=0 (must show only exact 31 Jan card):")
opts0 = options_for_package(p, date(2027,1,31), date(2027,2,12), adults=2, children=0, tolerance_days=0)
print(" count:", len(opts0), [o["departure_date"] for o in opts0])
ctx.pop()