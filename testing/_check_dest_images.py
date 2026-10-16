from app import create_app
from extensions import db
from models import Destination
from sqlalchemy import select

app = create_app()
with app.app_context():
    dests = list(db.session.scalars(select(Destination).order_by(Destination.name)))
    print(f"Total destinations: {len(dests)}")
    print()
    for d in dests:
        print(f"  id={d.id:>3} slug={d.slug!r:<25} hero_image_url={d.hero_image_url!r}")
