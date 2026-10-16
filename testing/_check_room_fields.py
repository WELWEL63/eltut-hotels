from app import create_app
from extensions import db
from models.room import Room

app = create_app()
with app.app_context():
    r = db.session.get(Room, 1022)
    print("Room fields:")
    for col in Room.__table__.columns:
        print(f"  {col.name}: {getattr(r, col.name, None)!r}")
