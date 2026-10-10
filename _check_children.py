from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.room_rate import RoomRate

app = create_app()
with app.app_context():
    total = db.session.scalar(select(func.count(RoomRate.id)))
    with_child = db.session.scalar(
        select(func.count(RoomRate.id)).where(RoomRate.child_price > 0)
    )
    zero_child = db.session.scalar(
        select(func.count(RoomRate.id)).where(RoomRate.child_price == 0)
    )
    null_child = db.session.scalar(
        select(func.count(RoomRate.id)).where(RoomRate.child_price.is_(None))
    )
    print(f"Total RoomRate rows:      {total}")
    print(f"  with child_price > 0:   {with_child}")
    print(f"  with child_price == 0:  {zero_child}")
    print(f"  with child_price NULL:  {null_child}")
