from app import create_app
from extensions import db
from services import recommendation_service
from models.hotel import Hotel

app = create_app()
with app.app_context():
    h = db.session.get(Hotel, 261)
    addons = recommendation_service.recommend_addons_for_hotel(h.id, limit=6)
    print(f"Add-ons: {len(addons)}")
    for a in addons[:3]:
        print(f"  id={a['id']} name={a['name']!r}")
        print(f"    price_adult={a['price_adult']} price_child={a['price_child']} currency={a['currency']}")
        print(f"    image_url={a['image_url']!r}")
