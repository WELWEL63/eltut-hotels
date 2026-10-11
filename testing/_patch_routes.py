p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Patch 1: pass hotel/room/destination AFTER pricing=pricing, ───
old1 = "        pricing=pricing,"
new1 = "        pricing=pricing,\n        hotel=meta.get('hotel'),\n        room=meta.get('room'),\n        destination=meta.get('destination'),"

if old1 in c:
    c = c.replace(old1, new1, 1)
    print("PATCH 1 OK")
else:
    print("PATCH 1 FAILED - anchor not found")
    raise SystemExit(1)

# ─── Patch 2: enrich _product_meta with hotel/room/destination ───
old2 = """        return {
            'name': f'{hotel.name if hotel else "Hotel"} — {product.type}',
            'slug': hotel.slug if hotel else None,
            'image': hotel.images[0].url if hotel and hotel.images else None,
            'adult_price': float(product.base_price_per_night),
            'child_price': float(product.base_price_per_night),
            'currency': 'EUR',
            'location': hotel.destination_id if hotel else None,
        }"""

new2 = """        dest = None
        if hotel and hotel.destination_id:
            from models import Destination  # noqa: PLC0415
            dest = db.session.get(Destination, hotel.destination_id)
        return {
            'name': f'{hotel.name if hotel else "Hotel"} — {product.type}',
            'slug': hotel.slug if hotel else None,
            'image': hotel.images[0].url if hotel and hotel.images else None,
            'adult_price': float(product.base_price_per_night),
            'child_price': float(product.base_price_per_night),
            'currency': 'EUR',
            'location': hotel.destination_id if hotel else None,
            'hotel': hotel.name if hotel else None,
            'room': product.type,
            'destination': dest.name if dest else None,
        }"""

if old2 in c:
    c = c.replace(old2, new2, 1)
    print("PATCH 2 OK")
else:
    print("PATCH 2 FAILED - anchor not found")
    raise SystemExit(1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)

print("ALL PATCHES APPLIED")
