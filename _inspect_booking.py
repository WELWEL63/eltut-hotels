from app import create_app
from extensions import db
from models import Booking, BookingItem
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()
b = db.session.scalar(select(Booking).order_by(Booking.id.desc()).limit(1))
print("booking:", b.reference, "total:", b.total_amount, "currency:", b.currency, "status:", b.status)
for it in db.session.scalars(select(BookingItem).where(BookingItem.booking_id == b.id)):
    print("  item:", it.item_type, it.product_type, it.product_id, it.product_name_snapshot, "qty", it.quantity, "unit", it.unit_price, "line", it.line_total)
ctx.pop()