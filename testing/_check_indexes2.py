from sqlalchemy import text
from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    idx = db.session.execute(text("""
        SELECT indexname FROM pg_indexes
        WHERE tablename = 'bookings'
        ORDER BY indexname
    """)).all()
    print("bookings indexes now:")
    for i in idx:
        print(f"  {i[0]!r}")
