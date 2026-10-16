from app import create_app
from extensions import db
from models.activity import Activity, ActivityPrice, ActivityImage
from services import recommendation_service

app = create_app()
with app.app_context():
    # Does Activity have .images?
    print("Activity has .images:", hasattr(Activity, "images"))
    # What columns does ActivityPrice have?
    print("ActivityPrice cols:", [c.name for c in ActivityPrice.__table__.columns])
    # What columns does ActivityImage have?
    print("ActivityImage cols:", [c.name for c in ActivityImage.__table__.columns])

    # Sample: does activity 513 have images?
    a = db.session.get(Activity, 513)
    print()
    print(f"Activity 513: {a.name!r}")
    print(f"  images: {len(a.images) if hasattr(a, 'images') else 'no rel'}")
    if hasattr(a, "images"):
        for img in list(a.images)[:3]:
            print(f"    url={img.url!r}")
