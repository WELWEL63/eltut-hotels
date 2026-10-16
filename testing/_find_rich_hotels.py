from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.hotel import Hotel, HotelFacility, HotelImage
from models.room import Room
from models.destination import Destination

app = create_app()
with app.app_context():
    # Subquery counts
    fac_count = (
        select(HotelFacility.hotel_id, func.count(HotelFacility.id).label("n"))
        .group_by(HotelFacility.hotel_id)
        .subquery()
    )
    img_count = (
        select(HotelImage.hotel_id, func.count(HotelImage.id).label("n"))
        .group_by(HotelImage.hotel_id)
        .subquery()
    )
    room_count = (
        select(Room.hotel_id, func.count(Room.id).label("n"))
        .group_by(Room.hotel_id)
        .subquery()
    )

    stmt = (
        select(
            Hotel.id, Hotel.name, Hotel.destination_id, Hotel.stars,
            func.coalesce(fac_count.c.n, 0).label("facilities"),
            func.coalesce(img_count.c.n, 0).label("images"),
            func.coalesce(room_count.c.n, 0).label("rooms"),
        )
        .outerjoin(fac_count, fac_count.c.hotel_id == Hotel.id)
        .outerjoin(img_count, img_count.c.hotel_id == Hotel.id)
        .outerjoin(room_count, room_count.c.hotel_id == Hotel.id)
        .order_by(
            (func.coalesce(img_count.c.n, 0) * 3
             + func.coalesce(fac_count.c.n, 0) * 2
             + func.coalesce(room_count.c.n, 0)).desc()
        )
        .limit(20)
    )
    rows = db.session.execute(stmt).all()

    print()
    print("TOP 20 HOTELS BY DATA RICHNESS")
    print("=" * 100)
    print(f"{'ID':>5}  {'NAME':<40} {'DEST':>5} {'★':>2} {'FAC':>4} {'IMG':>4} {'ROOMS':>6}")
    print("-" * 100)
    for r in rows:
        print(f"{r.id:>5}  {r.name[:39]:<40} {r.destination_id:>5} {r.stars:>2} "
              f"{r.facilities:>4} {r.images:>4} {r.rooms:>6}")

    print()
    print("SUMMARY STATS")
    print("=" * 100)
    total_hotels = db.session.scalar(select(func.count(Hotel.id)))
    hotels_with_images = db.session.scalar(
        select(func.count(func.distinct(HotelImage.hotel_id)))
    )
    hotels_with_facilities = db.session.scalar(
        select(func.count(func.distinct(HotelFacility.hotel_id)))
    )
    total_images = db.session.scalar(select(func.count(HotelImage.id)))
    total_facilities = db.session.scalar(select(func.count(HotelFacility.id)))
    print(f"  Total hotels        : {total_hotels}")
    print(f"  Hotels with images  : {hotels_with_images}")
    print(f"  Hotels with facil.  : {hotels_with_facilities}")
    print(f"  Total image rows    : {total_images}")
    print(f"  Total facility rows : {total_facilities}")
