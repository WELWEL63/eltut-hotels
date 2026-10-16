from app import create_app
from extensions import db
from models import Package, Destination
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()
sharm = db.session.scalar(select(Destination).where(Destination.slug == "sharm-el-sheikh"))
for p in db.session.scalars(select(Package).where(Package.destination_id == sharm.id).limit(3)):
    print(p.slug)
ctx.pop()