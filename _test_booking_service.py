from datetime import date
from app import create_app
from extensions import db
from services import booking_service

app = create_app()
with app.app_context():
    b = booking_service.create_booking(
        product_type="hotel",
        product_id=1022,
        travellers_adults=2,
        travellers_children=2,
        total_amount=847.70,
        currency="EUR",
        guest_email="test-smoke@example.com",
        guest_name="Smoke Test",
        guest_phone="+201234567890",
        check_in_date=date(2027, 1, 28),
        check_out_date=date(2027, 2, 4),
        how_heard="google",
        payment_method="paypal",
    )
    db.session.flush()
    print(f"Created booking: {b.reference}")
    print(f"  how_heard={b.how_heard!r}")
    print(f"  payment_method={b.payment_method!r}")
    print(f"  guest_name={b.guest_name!r}")
    print(f"  guest_phone={b.guest_phone!r}")
    db.session.rollback()
    print("Rolled back — no test data persisted")
