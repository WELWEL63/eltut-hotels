from app import create_app
from extensions import db
from models import Package

app = create_app()
with app.app_context():
    pkg = db.session.get(Package, 885)
    if pkg:
        print(f"Package 885: {pkg.name!r}")
        print(f"  slug: {pkg.slug!r}")
        print(f"  is_active: {pkg.is_active}")
        print()
        # Also show a few other packages
        from sqlalchemy import select
        rows = db.session.scalars(select(Package).limit(10)).all()
        print("Sample packages:")
        for p in rows:
            print(f"  id={p.id} slug={p.slug!r} name={p.name!r}")
