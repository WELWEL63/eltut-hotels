p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

old = '''    if product_type == PRODUCT_TYPE_HOTEL:
        hotel = db.session.get(Hotel, product.hotel_id)
        return {
            "name": f"{hotel.name if hotel else 'Hotel'} — {product.type}",
            "slug": hotel.slug if hotel else None,
            "image": hotel.images[0].url if hotel and hotel.images else None,
            "adult_price": float(product.base_price_per_night),
            "child_price": float(product.base_price_per_night),
            "currency": "EUR",
            "location": hotel.destination_id if hotel else None,
        }'''

new = '''    if product_type == PRODUCT_TYPE_HOTEL:
        hotel = db.session.get(Hotel, product.hotel_id)
        dest = None
        if hotel and hotel.destination_id:
            from models import Destination  # noqa: PLC0415
            dest = db.session.get(Destination, hotel.destination_id)
        return {
            "name": f"{hotel.name if hotel else 'Hotel'} — {product.type}",
            "slug": hotel.slug if hotel else None,
            "image": hotel.images[0].url if hotel and hotel.images else None,
            "adult_price": float(product.base_price_per_night),
            "child_price": float(product.base_price_per_night),
            "currency": "EUR",
            "location": hotel.destination_id if hotel else None,
            "hotel": hotel.name if hotel else None,
            "room": product.type,
            "destination": dest.name if dest else None,
        }'''

if old in c:
    c = c.replace(old, new, 1)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(c)
    print("✅ PATCH 2 APPLIED")
else:
    print("❌ STILL NOT MATCHING")
    idx = c.find("if product_type == PRODUCT_TYPE_HOTEL:")
    idx2 = c.find("if product_type == PRODUCT_TYPE_HOTEL:", idx + 10)
    print("Found second occurrence at", idx2)
    print("Exact bytes:")
    print(repr(c[idx2:idx2 + 500]))
    raise SystemExit(1)
