from datetime import date
from app import create_app
from extensions import db
from models import Package
from services.package_options_service import options_for_package

app = create_app()
ctx = app.app_context()
ctx.push()

p = db.session.get(Package, 919)
opts = options_for_package(p, date(2027,1,31), date(2027,2,12), adults=2, children=0)
print("options:", len(opts))
for o in opts:
    print(" ", o["id"], o["airline_name"], o["departure_date"], "nights", o["nights"],
          "per_adult", o["price_adult"], "grand", o["grand_total"],
          "land", o["land_total"], "flight", o["flight_total"],
          "markup", o["markup_total"], "tax", o["tax_total"], "transfer", o["transfer_total"])

# also check the app still boots routes
from blueprints.public.package_routes import package_detail, package_list
print("routes OK:", package_detail.__name__, package_list.__name__)
ctx.pop()