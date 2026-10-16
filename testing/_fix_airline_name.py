from app import create_app
from extensions import db
from models import Airline
from sqlalchemy import select

app = create_app()
with app.app_context():
    a = db.session.scalar(select(Airline).where(Airline.slug == "easyjet"))
    if a:
        old = a.name
        a.name = "EasyJet"
        db.session.commit()
        print(f"Renamed airline: {old!r} -> {a.name!r}")
    else:
        print("Airline 'easyjet' not found")
