path = "blueprints/public/booking_routes.py"
s = open(path, "r", encoding="utf-8").read()

old = '''        return {
            "name": f"{hotel.name if hotel else 'Hotel'} — {product.type}",
            "slug": hotel.slug if hotel else None,
            "image": hotel.images[0].url if hotel and hotel.images else None,
            "adult_price": float(product.base_price_per_night),
            "child_price": float(product.base_price_per_night),
            "currency": "GBP",
            "location": hotel.destination_id if hotel else None,
            "hotel": hotel.name if hotel else None,
            "room": product.type,
            "destination": dest.name if dest else None,
        }'''

new = '''        return {
            "name": f"{hotel.name if hotel else 'Hotel'} — {product.type}",
            "slug": hotel.slug if hotel else None,
            "image": hotel.images[0].url if hotel and hotel.images else None,
            "adult_price": float(product.base_price_per_night),
            "child_price": float(product.base_price_per_night),
            "currency": "GBP",
            "location": hotel.destination_id if hotel else None,
            "hotel": hotel.name if hotel else None,
            "room": product.type,
            "meal_plan": (product.meal_plan or "") if hasattr(product, "meal_plan") else "",
            "max_occupancy": getattr(product, "max_occupancy", None),
            "stars": hotel.stars if hotel else None,
            "address": hotel.address if hotel else None,
            "destination": dest.name if dest else None,
            "hotel_slug": hotel.slug if hotel else None,
            "room_id": product.id,
        }'''

assert old in s, "hotel meta block not found"
s = s.replace(old, new, 1)
open(path, "w", encoding="utf-8").write(s)
print("_product_meta hotel branch enriched")