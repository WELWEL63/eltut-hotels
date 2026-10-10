from app import create_app
app = create_app()
with app.app_context():
    from services import quote_service
    q = quote_service.create_draft(
        customer_email="test@example.com",
        customer_name="Test Customer",
        product_type="package",
        product_id=527,
        product_name_snapshot="AMZING REDSEA",
    )
    print(f"Draft created: {q.reference}")
    print(f"Visit: http://127.0.0.1:5000/admin/quotes/{q.reference}")
