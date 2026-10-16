from app import create_app
from extensions import db
from models import Booking, BookingItem, Hotel, Activity, Destination
from sqlalchemy import select

app = create_app()
ctx = app.app_context()
ctx.push()

b = db.session.scalar(select(Booking).where(Booking.reference == "ELT-2026-76419"))
print("booking:", b.reference, "product_type:", b.product_type, "product_id:", b.product_id, "total:", b.total_amount, b.currency)
print("check_in:", b.check_in_date, "check_out:", b.check_out_date, "adults:", b.travellers_adults, "children:", b.travellers_children)
items = list(db.session.scalars(select(BookingItem).where(BookingItem.booking_id == b.id).order_by(BookingItem.id)))
print("items:", len(items))
for it in items:
    print("  ", it.item_type, it.product_type, it.product_id, "|", it.product_name_snapshot, "| line", it.line_total)
primary = next((i for i in items if i.item_type == "primary"), items[0] if items else None)
if primary:
    print("primary product_id:", primary.product_id, "product_type:", primary.product_type)
    # What does the primary's product_id actually point at?
    h = db.session.get(Hotel, primary.product_id)
    a = db.session.get(Activity, primary.product_id)
    print("  Hotel id match:", h.name if h else None)
    print("  Activity id match:", a.name if a else None)
ctx.pop()