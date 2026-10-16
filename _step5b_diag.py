from datetime import date
from app import create_app
from extensions import db
from models import Package, Room, RoomRate
from services.package_pricing_service import _rate_for_room

app = create_app()
ctx = app.app_context()
ctx.push()
for pid in [537, 540, 594, 528, 529, 534, 1165]:
    p = db.session.get(Package, pid)
    if not p: continue
    r = db.session.get(Room, p.room_id) if p.room_id else None
    rates = list(db.session.scalars(
        __import__("sqlalchemy").select(RoomRate).where(RoomRate.room_id == p.room_id)
    )) if p.room_id else []
    nightly = _rate_for_room(p.room_id, date(2027,1,31), date(2027,2,12)) if p.room_id else (None, None)
    print(f"pkg {pid} dest={p.destination_id} room={p.room_id} room_obj={'Y' if r else 'N'} base={r.base_price_per_night if r else None} rates={len(rates)} -> nightly={nightly}")
ctx.pop()