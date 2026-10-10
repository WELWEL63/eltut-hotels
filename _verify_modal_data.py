from app import create_app
from extensions import db
from services import recommendation_service
from models.hotel import Hotel

app = create_app()
with app.app_context():
    addons = recommendation_service.recommend_addons_for_hotel(261, limit=2)
    for a in addons:
        print(f"--- {a['name']} ---")
        print(f"  description: {a.get('description', '')[:80]!r}...")
        print(f"  departure_time: {a.get('departure_time')!r}")
        print(f"  meeting_point: {a.get('meeting_point')!r}")
        print(f"  what_to_bring: {a.get('what_to_bring', '')[:60]!r}...")
        print()
