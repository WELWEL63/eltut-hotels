from app import create_app
from extensions import db
from models import Package, PackageFlight
from services.package_pricing_service import compute_package_flight_card

app = create_app()
ctx = app.app_context()
ctx.push()

p = db.session.get(Package, 919)
for c in db.session.query(PackageFlight).filter_by(package_id=p.id).all():
    r = compute_package_flight_card(p, c)
    print("card", c.id,
          "| airline=", r["airline_name"],
          "| from=", r["flight_from"], "to=", r["flight_to"],
          "| dep=", r["departure_date"], "ret=", r["return_date"],
          "| nights=", r["nights"],
          "| hotel=", round(r["hotel_total"], 2),
          "| flights=", round(r["flight_total"], 2),
          "| markup=", round(r["markup"], 2),
          "| tax=", round(r["tax"], 2),
          "| per_person=", round(r["per_person"], 2),
          "| est=", r["return_estimated"])
ctx.pop()