from app import create_app
from extensions import db
from models import Flight
from sqlalchemy import select, func

app = create_app()
with app.app_context():
    rows = db.session.execute(
        select(Flight.airline_name, func.count(Flight.id))
        .group_by(Flight.airline_name)
        .order_by(func.count(Flight.id).desc())
    ).all()
    print(f"Unique airline_name values in flights ({len(rows)}):")
    for name, cnt in rows:
        print(f"  {name!r:<25} -> {cnt} flights")
