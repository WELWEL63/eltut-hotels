from app import create_app
from extensions import db
from models import Destination

app = create_app()
ctx = app.app_context()
ctx.push()
for d in db.session.scalars(__import__("sqlalchemy").select(Destination).order_by(Destination.name)):
    print(f"{d.slug:<24} bookable={d.is_bookable}")
ctx.pop()