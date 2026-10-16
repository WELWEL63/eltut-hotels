from app import create_app
from extensions import db
from models import Destination
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()
changed = 0
for d in db.session.scalars(select(Destination)):
    if not d.is_bookable:
        d.is_bookable = True
        changed += 1
db.session.commit()
print(f"flipped {changed} destinations back to bookable")
for d in db.session.scalars(select(Destination).order_by(Destination.name)):
    print(f"  {d.slug:24} bookable={d.is_bookable}")
ctx.pop()