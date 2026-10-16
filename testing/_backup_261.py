import json
from sqlalchemy import select
from app import create_app
from extensions import db
from models.hotel import Hotel, HotelFacility, HotelImage

app = create_app()
with app.app_context():
    h = db.session.get(Hotel, 261)
    if not h:
        print("Hotel 261 not found")
        raise SystemExit(1)
    facs = db.session.scalars(
        select(HotelFacility).where(HotelFacility.hotel_id == h.id)
    ).all()
    imgs = db.session.scalars(
        select(HotelImage).where(HotelImage.hotel_id == h.id)
    ).all()
    backup = {
        "hotel": {
            "id": h.id, "name": h.name, "slug": h.slug,
            "destination_id": h.destination_id, "stars": h.stars,
            "address": h.address, "latitude": str(h.latitude) if h.latitude else None,
            "longitude": str(h.longitude) if h.longitude else None,
            "description": h.description,
            "check_in_time": h.check_in_time, "check_out_time": h.check_out_time,
            "total_capacity": h.total_capacity, "is_active": h.is_active,
            "useful_tips": h.useful_tips, "house_rules": h.house_rules,
            "check_in_details": h.check_in_details,
            "cancellation_policy": h.cancellation_policy,
            "neighborhood_info": h.neighborhood_info,
            "google_maps_url": h.google_maps_url,
        },
        "facilities": [
            {"id": f.id, "name": f.name, "type": f.type,
             "quantity": f.quantity, "notes": f.notes}
            for f in facs
        ],
        "images": [
            {"id": im.id, "url": im.url, "type": im.type,
             "sort_order": im.sort_order, "media_type": im.media_type,
             "poster_url": im.poster_url}
            for im in imgs
        ],
    }
    with open("_backup_hotel_261.json", "w", encoding="utf-8") as f:
        json.dump(backup, f, indent=2, default=str, ensure_ascii=False)
    print(f"Backup written to _backup_hotel_261.json")
    print(f"  hotel fields: {len(backup['hotel'])}")
    print(f"  facilities : {len(backup['facilities'])}")
    print(f"  images     : {len(backup['images'])}")
