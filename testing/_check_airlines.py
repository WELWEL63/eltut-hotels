from app import create_app
from extensions import db
from models import Airline
from sqlalchemy import select

app = create_app()
with app.app_context():
    airlines = list(db.session.scalars(select(Airline)))
    print(f"Airlines in DB: {len(airlines)}")
    for a in airlines:
        print(f"  id={a.id} name={a.name!r} slug={a.slug!r}")
