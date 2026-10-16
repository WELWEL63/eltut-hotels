from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.room_rate import RoomRate

app = create_app()
with app.app_context():
    earliest_from = db.session.scalar(select(func.min(RoomRate.valid_from)))
    latest_to = db.session.scalar(select(func.max(RoomRate.valid_to)))
    null_from = db.session.scalar(
        select(func.count(RoomRate.id)).where(RoomRate.valid_from.is_(None))
    )
    null_to = db.session.scalar(
        select(func.count(RoomRate.id)).where(RoomRate.valid_to.is_(None))
    )
    print(f"Earliest valid_from: {earliest_from}")
    print(f"Latest valid_to:     {latest_to}")
    print(f"Rows with valid_from NULL: {null_from}")
    print(f"Rows with valid_to   NULL: {null_to}")

    # Sample 5 rows to see the shape
    print()
    print("Sample rows:")
    rows = db.session.scalars(select(RoomRate).limit(5)).all()
    for r in rows:
        print(f"  room={r.room_id} adult={r.adult_price} child={r.child_price} "
              f"from={r.valid_from} to={r.valid_to}")
