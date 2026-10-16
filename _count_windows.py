from app import create_app
from extensions import db
from models import Package, PackagePrice
from sqlalchemy import select, func

app = create_app()
ctx = app.app_context()
ctx.push()

pkg = db.session.scalar(select(Package).where(Package.slug == "hurghada-iberotel-club-fanar-standard-room-pool-garden-view"))

total = db.session.scalar(
    select(func.count(PackagePrice.id)).where(PackagePrice.package_id == pkg.id)
)
print(f"Total price windows for this package: {total}")
print()

min_date = db.session.scalar(
    select(func.min(PackagePrice.valid_from)).where(PackagePrice.package_id == pkg.id)
)
max_date = db.session.scalar(
    select(func.max(PackagePrice.valid_to)).where(PackagePrice.package_id == pkg.id)
)
print(f"Date range of windows: {min_date} -> {max_date}")
print()

# What windows exist in Jan 2027?
from datetime import date
print("Windows overlapping Jan 2027:")
rows = db.session.scalars(
    select(PackagePrice)
    .where(
        PackagePrice.package_id == pkg.id,
        PackagePrice.valid_from <= date(2027, 2, 1),
        PackagePrice.valid_to >= date(2027, 1, 1),
    )
    .order_by(PackagePrice.valid_from)
).all()
print(f"  {len(rows)} windows found")
for p in rows[:20]:
    nights = (p.valid_to - p.valid_from).days if p.valid_from and p.valid_to else "?"
    print(f"  {p.valid_from} -> {p.valid_to}  ({nights}n)  EUR {p.adult_price}")