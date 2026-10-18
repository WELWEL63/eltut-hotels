from app import create_app
from extensions import db
from models import Package
from services.package_options_service import options_for_package
from datetime import date

app = create_app()
ctx = app.app_context()
ctx.push()

p = db.session.get(Package, 760)
print("Package:", p.name if p else "NOT FOUND")

opts = options_for_package(
    p, date(2026, 11, 21), date(2026, 11, 28),
    adults=3, children=0, tolerance_days=30,
)
print("Options:", len(opts))
for o in opts[:3]:
    print("  is_land_only=", o.get("is_land_only"),
          "per_person=", o.get("per_person"),
          "grand_total=", o.get("grand_total"))

ctx.pop()