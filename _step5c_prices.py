from app import create_app
from extensions import db
from models import Package, PackagePrice
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()
for pid in [537, 540, 594, 528, 529, 534, 1165, 1525, 1151, 643, 2172, 526, 725, 935, 1526, 1592]:
    p = db.session.get(Package, pid)
    if not p: continue
    prices = list(db.session.scalars(select(PackagePrice).where(PackagePrice.package_id == pid).limit(3)))
    print(f"pkg {pid:5} {p.name[:38]:40} prices={len(prices)}", "adult=" + str(prices[0].adult_price) if prices else "")
ctx.pop()