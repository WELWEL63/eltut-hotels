from sqlalchemy import text
from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    # Columns
    cols = db.session.execute(text("""
        SELECT column_name, data_type, character_maximum_length
        FROM information_schema.columns
        WHERE table_name = 'bookings'
        ORDER BY ordinal_position
    """)).all()
    print("bookings columns:")
    for c in cols:
        print(f"  {c[0]!r}: {c[1]}{f'({c[2]})' if c[2] else ''}")

    # Indexes
    print()
    idx = db.session.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'bookings'
        ORDER BY indexname
    """)).all()
    print("bookings indexes:")
    for i in idx:
        print(f"  {i[0]!r}")
