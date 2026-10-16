from sqlalchemy import select, func
from app import create_app
from extensions import db
from models.hotel import Hotel, HotelFacility, HotelImage

app = create_app()
with app.app_context():
    print("=" * 70)
    print("HOTEL MODEL — columns")
    print("=" * 70)
    for col in Hotel.__table__.columns:
        print(f"  {col.name:<25} {str(col.type):<25} nullable={col.nullable}")

    print()
    print("=" * 70)
    print("HOTEL FACILITY — columns")
    print("=" * 70)
    for col in HotelFacility.__table__.columns:
        print(f"  {col.name:<25} {str(col.type):<25} nullable={col.nullable}")

    print()
    print("=" * 70)
    print("HOTEL IMAGE — columns")
    print("=" * 70)
    for col in HotelImage.__table__.columns:
        print(f"  {col.name:<25} {str(col.type):<25} nullable={col.nullable}")

    print()
    print("=" * 70)
    print("SAMPLE — Sunny Days El Palacio (Hurghada)")
    print("=" * 70)
    h = db.session.scalars(
        select(Hotel).where(Hotel.name.ilike("%Sunny Days El Palacio%")).limit(1)
    ).first()
    if h:
        print(f"id={h.id} name={h.name!r} slug={h.slug!r} stars={h.stars}")
        print(f"address={h.address!r}")
        print(f"check_in_time={h.check_in_time!r} check_out_time={h.check_out_time!r}")
        print(f"total_capacity={h.total_capacity}")
        print(f"description[:200]={(h.description or '')[:200]!r}")
        print(f"google_maps_url={h.google_maps_url!r}")
        print(f"useful_tips[:100]={(h.useful_tips or '')[:100]!r}")
        print(f"neighborhood_info[:100]={(h.neighborhood_info or '')[:100]!r}")
        print(f"house_rules[:100]={(h.house_rules or '')[:100]!r}")
        print(f"cancellation_policy[:100]={(h.cancellation_policy or '')[:100]!r}")

        n_fac = db.session.scalar(
            select(func.count(HotelFacility.id)).where(HotelFacility.hotel_id == h.id)
        )
        n_img = db.session.scalar(
            select(func.count(HotelImage.id)).where(HotelImage.hotel_id == h.id)
        )
        print(f"facility rows: {n_fac}")
        print(f"image rows:    {n_img}")

        # sample facilities
        facs = db.session.scalars(
            select(HotelFacility).where(HotelFacility.hotel_id == h.id).limit(10)
        ).all()
        print("sample facilities:")
        for f in facs:
            print(f"  - name={f.name!r} type={f.type!r} qty={f.quantity} notes={f.notes!r}")

        # sample images
        imgs = db.session.scalars(
            select(HotelImage).where(HotelImage.hotel_id == h.id).limit(5)
        ).all()
        print("sample images:")
        for im in imgs:
            print(f"  - url={im.url!r} type={im.type!r} sort={im.sort_order}")
    else:
        print("Sunny Days El Palacio not found — using any Hurghada hotel")
        h = db.session.scalars(
            select(Hotel).where(Hotel.destination_id == 27).limit(1)
        ).first()
        if h:
            print(f"Found: id={h.id} name={h.name!r}")
