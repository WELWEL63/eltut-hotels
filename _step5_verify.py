from datetime import date
from app import create_app
from extensions import db
from models import Package, Destination
from services.package_options_service import options_for_package
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()

# --- Land-only: any Sharm package ---
sharm_dest = db.session.scalar(select(Destination).where(Destination.slug == "sharm-el-sheikh"))
sharm_pkg = db.session.scalar(select(Package).where(Package.destination_id == sharm_dest.id).limit(1))
print("SHARM pkg:", sharm_pkg.id, sharm_pkg.name[:50])
opts = options_for_package(sharm_pkg, date(2027,1,31), date(2027,2,12), adults=2, children=0)
print("  options:", len(opts))
for o in opts:
    print("   ", o["label"], "nights", o["nights"], "per_adult", o["price_adult"], "grand", o["grand_total"], "land_only", o.get("is_land_only"))

# --- Package with cards still uses real cards ---
hurghada_pkg = db.session.get(Package, 919)
opts = options_for_package(hurghada_pkg, date(2027,1,31), date(2027,2,12), adults=2, children=0)
print()
print("HURGHADA pkg 919 options:", len(opts))
for o in opts:
    print("   ", o["airline_name"], o["departure_date"], "per_adult", o["price_adult"], "grand", o["grand_total"], "land_only", o.get("is_land_only", False))

ctx.pop()