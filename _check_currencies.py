from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    print("=" * 60)
    print("Current activity price currencies")
    print("=" * 60)
    rows = db.session.execute(text("""
        SELECT currency, COUNT(*) FROM activity_prices
        GROUP BY currency ORDER BY currency
    """)).all()
    for cur, count in rows:
        print(f"  {cur!r}: {count} rows")

    print()
    print("=" * 60)
    print("Room rate currencies")
    print("=" * 60)
    rows = db.session.execute(text("""
        SELECT currency, COUNT(*) FROM room_rates
        GROUP BY currency ORDER BY currency
    """)).all()
    for cur, count in rows:
        print(f"  {cur!r}: {count} rows")

    print()
    print("=" * 60)
    print("Package price currencies")
    print("=" * 60)
    rows = db.session.execute(text("""
        SELECT currency, COUNT(*) FROM package_prices
        GROUP BY currency ORDER BY currency
    """)).all()
    for cur, count in rows:
        print(f"  {cur!r}: {count} rows")
