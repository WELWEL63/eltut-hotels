from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    # Show before
    before = db.session.execute(text("""
        SELECT currency, COUNT(*) FROM activity_prices
        GROUP BY currency ORDER BY currency
    """)).all()
    print("BEFORE:")
    for cur, count in before:
        print(f"  {cur!r}: {count} rows")

    # Update
    result = db.session.execute(text("""
        UPDATE activity_prices SET currency = 'EUR' WHERE currency = 'USD'
    """))
    print(f"\nUpdated {result.rowcount} rows")
    db.session.commit()

    # Show after
    after = db.session.execute(text("""
        SELECT currency, COUNT(*) FROM activity_prices
        GROUP BY currency ORDER BY currency
    """)).all()
    print("\nAFTER:")
    for cur, count in after:
        print(f"  {cur!r}: {count} rows")
