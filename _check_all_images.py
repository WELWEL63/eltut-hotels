from app import create_app
app = create_app()
with app.app_context():
    from extensions import db
    from models import ActivityImage, HotelImage, PackageImage
    from sqlalchemy import select

    print("=== activity_images ===")
    for img in db.session.scalars(select(ActivityImage).order_by(ActivityImage.id.desc()).limit(20)):
        print(f"  id={img.id:3d} act={img.activity_id:4d} media={img.media_type:5s} url={img.url.split('/')[-1]!r}")

    print(f"\n=== hotel_images ===")
    for img in db.session.scalars(select(HotelImage).order_by(HotelImage.id.desc()).limit(20)):
        print(f"  id={img.id:3d} hotel={img.hotel_id:4d} media={img.media_type:5s} url={img.url.split('/')[-1]!r}")

    print(f"\n=== package_images ===")
    for img in db.session.scalars(select(PackageImage).order_by(PackageImage.id.desc()).limit(20)):
        print(f"  id={img.id:3d} pkg={img.package_id:4d} media={img.media_type:5s} url={img.url.split('/')[-1]!r}")
