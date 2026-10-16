from app import create_app
from extensions import db
from models import Destination
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()
d = db.session.scalar(select(Destination).where(Destination.slug == "sharm-el-sheikh"))
d.is_bookable = True
db.session.commit()
print("sharm is_bookable ->", d.is_bookable)
ctx.pop()