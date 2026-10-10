from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.room import Room

app = create_app()
with app.app_context():
    print("Room max_occupancy distribution:")
    rows = db.session.execute(
        select(Room.max_occupancy, func.count(Room.id))
        .group_by(Room.max_occupancy)
        .order_by(Room.max_occupancy)
    ).all()
    for mo, c in rows:
        print(f"  max_occupancy={mo!r:<6} -> {c} rooms")

    print()
    print("Hotel 261 rooms:")
    rows = db.session.execute(
        select(Room.id, Room.type, Room.max_occupancy, Room.capacity)
        .where(Room.hotel_id == 261)
    ).all()
    for r in rows:
        print(f"  id={r.id} type={r.type!r} max_occ={r.max_occupancy} cap={r.capacity}")
