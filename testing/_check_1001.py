from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.hotel import Hotel, HotelFacility, HotelImage, HotelFAQ, HotelTip
from models.destination import Destination
from models.room import Room
from models.room_rate import RoomRate

app = create_app()
with app.app_context():
    h = db.session.get(Hotel, 1001)
    if not h:
        print("Hotel id=1001 not found")
        raise SystemExit(1)

    dest = db.session.get(Destination, h.destination_id)

    print("=" * 72)
    print(f"HOTEL 1001 — {h.name}")
    print("=" * 72)
    print(f"  id               : {h.id}")
    print(f"  name             : {h.name!r}")
    print(f"  slug             : {h.slug!r}")
    print(f"  destination      : {dest.name if dest else '?'} (id={h.destination_id})")
    print(f"  stars            : {h.stars}")
    print(f"  is_active        : {h.is_active}")
    print(f"  total_capacity   : {h.total_capacity}")
    print(f"  address          : {h.address!r}")
    print(f"  latitude         : {h.latitude}")
    print(f"  longitude        : {h.longitude}")
    print(f"  check_in_time    : {h.check_in_time!r}")
    print(f"  check_out_time   : {h.check_out_time!r}")
    print(f"  google_maps_url  : {h.google_maps_url!r}")
    print()
    print(f"  description[:300]      : {(h.description or '')[:300]!r}")
    print(f"  useful_tips[:300]      : {(h.useful_tips or '')[:300]!r}")
    print(f"  house_rules[:300]      : {(h.house_rules or '')[:300]!r}")
    print(f"  check_in_details[:300] : {(h.check_in_details or '')[:300]!r}")
    print(f"  cancellation_policy[:300]: {(h.cancellation_policy or '')[:300]!r}")
    print(f"  neighborhood_info[:300]: {(h.neighborhood_info or '')[:300]!r}")

    print()
    print("-" * 72)
    print("FACILITIES")
    print("-" * 72)
    facs = db.session.scalars(
        select(HotelFacility).where(HotelFacility.hotel_id == h.id)
    ).all()
    print(f"  total: {len(facs)}")
    for f in facs:
        print(f"    [{f.type:<10}] {f.name!r:<40} qty={f.quantity} notes={f.notes!r}")

    print()
    print("-" * 72)
    print("IMAGES")
    print("-" * 72)
    imgs = db.session.scalars(
        select(HotelImage).where(HotelImage.hotel_id == h.id).order_by(HotelImage.sort_order)
    ).all()
    print(f"  total: {len(imgs)}")
    for im in imgs[:15]:
        print(f"    sort={im.sort_order:<3} type={im.type:<10} media={im.media_type:<8} url={im.url!r}")

    print()
    print("-" * 72)
    print("ROOMS")
    print("-" * 72)
    rooms = db.session.scalars(
        select(Room).where(Room.hotel_id == h.id)
    ).all()
    print(f"  total: {len(rooms)}")
    for r in rooms[:10]:
        rates = db.session.scalars(
            select(RoomRate).where(RoomRate.room_id == r.id)
        ).all()
        print(f"    room id={r.id} type={r.type!r} active={r.is_active} "
              f"max_occ={r.max_occupancy} cap={r.capacity} "
              f"base={r.base_price_per_night} rates={len(rates)}")

    print()
    print("-" * 72)
    print("FAQs / TIPS")
    print("-" * 72)
    faqs = db.session.scalars(select(HotelFAQ).where(HotelFAQ.hotel_id == h.id)).all()
    tips = db.session.scalars(select(HotelTip).where(HotelTip.hotel_id == h.id)).all()
    print(f"  faqs: {len(faqs)}  tips: {len(tips)}")
    for q in faqs[:5]:
        print(f"    Q: {q.question!r}")
        print(f"    A: {(q.answer or '')[:100]!r}")
