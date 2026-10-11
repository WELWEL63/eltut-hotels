from sqlalchemy import text
from app import create_app
from extensions import db

app = create_app()
with app.app_context():
    # PostgreSQL: query the constraint definition
    rows = db.session.execute(text("""
        SELECT con.conname, pg_get_constraintdef(con.oid)
        FROM pg_constraint con
        JOIN pg_class rel ON rel.oid = con.conrelid
        WHERE rel.relname = 'hotel_facilities'
          AND con.contype = 'c'
    """)).all()
    print("=" * 70)
    print("CHECK constraints on hotel_facilities")
    print("=" * 70)
    for name, definition in rows:
        print(f"  {name}")
        print(f"    {definition}")
        print()

    # Also: what distinct types already exist?
    print("=" * 70)
    print("Distinct facility types currently in the table")
    print("=" * 70)
    from models.hotel import HotelFacility
    from sqlalchemy import select, func
    rows = db.session.execute(
        select(HotelFacility.type, func.count(HotelFacility.id))
        .group_by(HotelFacility.type)
    ).all()
    for t, c in rows:
        print(f"  {t!r:<20} : {c} rows")
