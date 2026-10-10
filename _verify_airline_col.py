from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()
with app.app_context():
    rows = db.session.execute(text("""
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_name = 'flights' AND column_name = 'airline_id'
    """)).all()
    print("airline_id column:", rows)
    print("exists:", len(rows) > 0)
