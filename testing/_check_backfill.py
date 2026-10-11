from app import create_app
from extensions import db
from models import Flight
from sqlalchemy import select, func

app = create_app()
with app.app_context():
    # Total flights
    total = db.session.scalar(select(func.count(Flight.id)))
    print(f"Total flights: {total}")

    # Linked vs unlinked
    linked = db.session.scalar(
        select(func.count(Flight.id)).where(Flight.airline_id.is_not(None))
    )
    unlinked = db.session.scalar(
        select(func.count(Flight.id)).where(Flight.airline_id.is_(None))
    )
    print(f"  with airline_id: {linked}")
    print(f"  without airline_id: {unlinked}")

    # Breakdown
    print()
    print("Grouped by airline_id:")
    rows = db.session.execute(
        select(Flight.airline_id, func.count(Flight.id))
        .group_by(Flight.airline_id)
    ).all()
    for aid, cnt in rows:
        print(f"  airline_id={aid} -> {cnt} flights")
