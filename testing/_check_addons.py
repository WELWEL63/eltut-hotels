from app import create_app
from extensions import db
from services import recommendation_service
from models.hotel import Hotel

app = create_app()
with app.app_context():
    h = db.session.get(Hotel, 261)
    addons = recommendation_service.recommend_addons_for_hotel(h.id, limit=6)
    print(f"Add-ons returned: {len(addons)}")
    for a in addons[:3]:
        print()
        print(f"  keys: {sorted(a.keys())}")
        for k, v in a.items():
            print(f"    {k}: {v!r}")
