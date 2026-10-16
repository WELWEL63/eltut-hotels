from app import create_app
from extensions import db
from sqlalchemy import text

app = create_app()
ctx = app.app_context()
ctx.push()

row = db.session.execute(text(
    "select column_name, data_type, is_nullable, column_default "
    "from information_schema.columns "
    "where table_name='destinations' and column_name='is_bookable'"
)).fetchone()
print("column row:", row)

n = db.session.execute(text("select count(*) from destinations where is_bookable=true")).scalar()
print("is_bookable=true count:", n)

t = db.session.execute(text("select count(*) from destinations")).scalar()
print("total destinations:", t)

ctx.pop()