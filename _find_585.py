from app import create_app
from extensions import db
from models import Package, PackagePrice
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()

pkg = db.session.scalar(select(Package).where(Package.slug == "hurghada-iberotel-club-fanar-standard-room-pool-garden-view"))

# Find any window with adult_price near 585
rows = db.session.scalars(
    select(PackagePrice)
    .where(
        PackagePrice.package_id == pkg.id,
        PackagePrice.adult_price >= 580,
        PackagePrice.adult_price <= 590,
    )
).all()

print(f"Windows with adult_price between 580-590: {len(rows)}")
for r in rows:
    print(f"  id={r.id}  {r.valid_from} -> {r.valid_to}  EUR {r.adult_price}")

print()
print("=" * 60)
print("What _first_package_price() returns (id ASC)")
print("=" * 60)
first = db.session.scalar(
    select(PackagePrice)
    .where(PackagePrice.package_id == pkg.id)
    .order_by(PackagePrice.id)
    .limit(1)
)
if first:
    print(f"  id={first.id}")
    print(f"  window: {first.valid_from} -> {first.valid_to}")
    print(f"  adult_price: {first.adult_price}")
    print(f"  currency: {first.currency}")

print()
print("=" * 60)
print("First 5 by id ASC")
print("=" * 60)
top5 = db.session.scalars(
    select(PackagePrice)
    .where(PackagePrice.package_id == pkg.id)
    .order_by(PackagePrice.id)
    .limit(5)
).all()
for r in top5:
    print(f"  id={r.id}  {r.valid_from} -> {r.valid_to}  EUR {r.adult_price}")