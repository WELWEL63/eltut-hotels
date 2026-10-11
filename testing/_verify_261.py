from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.hotel import Hotel, HotelFacility, HotelImage
from models.room import Room

app = create_app()
with app.app_context():
    h = db.session.get(Hotel, 261)
    print("=" * 70)
    print(f"FINAL STATE: Hotel {h.id} - {h.name!r}")
    print("=" * 70)
    print(f"  slug              : {h.slug}")
    print(f"  destination_id    : {h.destination_id}")
    print(f"  stars             : {h.stars}")
    print(f"  address           : {h.address!r}")
    print(f"  latitude          : {h.latitude}")
    print(f"  longitude         : {h.longitude}")
    print(f"  check_in_time     : {h.check_in_time!r}")
    print(f"  check_out_time    : {h.check_out_time!r}")
    print(f"  total_capacity    : {h.total_capacity}")
    print(f"  google_maps_url   : {h.google_maps_url[:60] + '...' if h.google_maps_url else None!r}")
    print()
    print(f"  description       : {len(h.description or '')} chars")
    print(f"  useful_tips       : {len(h.useful_tips or '')} chars")
    print(f"  house_rules       : {len(h.house_rules or '')} chars")
    print(f"  check_in_details  : {len(h.check_in_details or '')} chars")
    print(f"  cancellation_policy: {len(h.cancellation_policy or '')} chars")
    print(f"  neighborhood_info : {len(h.neighborhood_info or '')} chars")

    print()
    print("-" * 70)
    print("FACILITIES")
    print("-" * 70)
    facs = db.session.scalars(
        select(HotelFacility).where(HotelFacility.hotel_id == h.id).order_by(HotelFacility.id)
    ).all()
    print(f"  total: {len(facs)}")
    for f in facs:
        print(f"    [{f.type:<10}] {f.name!r:<25} qty={f.quantity} notes={f.notes!r}")

    print()
    print("-" * 70)
    print("IMAGES")
    print("-" * 70)
    imgs = db.session.scalars(
        select(HotelImage).where(HotelImage.hotel_id == h.id).order_by(HotelImage.sort_order)
    ).all()
    print(f"  total: {len(imgs)}")
    for im in imgs:
        print(f"    sort={im.sort_order:<4} type={im.type:<12} url={im.url[-45:]!r}")

    print()
    print("-" * 70)
    print("ROOMS")
    print("-" * 70)
    rooms = db.session.scalars(
        select(Room).where(Room.hotel_id == h.id)
    ).all()
    print(f"  total: {len(rooms)}")
    for r in rooms:
        print(f"    id={r.id} type={r.type!r} base={r.base_price_per_night}")
