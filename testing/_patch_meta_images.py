p = 'blueprints/public/booking_routes.py'
with open(p, encoding='utf-8') as f:
    c = f.read()

# ─── Patch 1: fix activity image URL (prepend /static if relative) ───
old1 = '''        return {
            "name": product.name,
            "slug": product.slug,
            "image": product.images[0].url if product.images else None,
            "adult_price": float(price_row.adult_price) if price_row else None,
            "child_price": float(price_row.child_price) if price_row else None,
            "currency": price_row.currency if price_row else "EUR",
            "location": product.destination_id,
        }'''

new1 = '''        img_url = product.images[0].url if product.images else None
        if img_url and not (img_url.startswith("http") or img_url.startswith("/static")):
            img_url = "/static" + (img_url if img_url.startswith("/") else "/" + img_url)
        return {
            "name": product.name,
            "slug": product.slug,
            "image": img_url,
            "adult_price": float(price_row.adult_price) if price_row else None,
            "child_price": float(price_row.child_price) if price_row else None,
            "currency": price_row.currency if price_row else "EUR",
            "location": product.destination_id,
        }'''

if old1 in c:
    c = c.replace(old1, new1, 1)
    print("✅ Patch 1: activity image URL fixed")
else:
    print("❌ Patch 1 FAILED — activity anchor not found")
    idx = c.find("if product_type == PRODUCT_TYPE_ACTIVITY:")
    print("Context:", repr(c[idx:idx + 500]))
    raise SystemExit(1)

# ─── Patch 2: enrich package meta with hotel/room/destination + image ───
old2 = '''    if product_type == PRODUCT_TYPE_PACKAGE:
        price_row = db.session.scalar(
            select(PackagePrice)
            .where(PackagePrice.package_id == product.id)
            .order_by(PackagePrice.id).limit(1)
        )
        return {
            "name": product.name,
            "slug": product.slug,
            "image": product.images[0].url if product.images else None,
            "adult_price": float(price_row.adult_price) if price_row else None,
            "child_price": float(price_row.child_price) if price_row else None,
            "currency": price_row.currency if price_row else "EUR",
            "location": product.destination_id,
        }'''

new2 = '''    if product_type == PRODUCT_TYPE_PACKAGE:
        price_row = db.session.scalar(
            select(PackagePrice)
            .where(PackagePrice.package_id == product.id)
            .order_by(PackagePrice.id).limit(1)
        )
        dest = None
        if product.destination_id:
            from models import Destination  # noqa: PLC0415
            dest = db.session.get(Destination, product.destination_id)
        img_url = product.images[0].url if product.images else None
        if img_url and not (img_url.startswith("http") or img_url.startswith("/static")):
            img_url = "/static" + (img_url if img_url.startswith("/") else "/" + img_url)
        return {
            "name": product.name,
            "slug": product.slug,
            "image": img_url,
            "adult_price": float(price_row.adult_price) if price_row else None,
            "child_price": float(price_row.child_price) if price_row else None,
            "currency": price_row.currency if price_row else "EUR",
            "location": product.destination_id,
            "hotel": None,
            "room": None,
            "destination": dest.name if dest else None,
        }'''

if old2 in c:
    c = c.replace(old2, new2, 1)
    print("✅ Patch 2: package meta enriched with destination + image fix")
else:
    print("❌ Patch 2 FAILED — package anchor not found")
    raise SystemExit(1)

with open(p, 'w', encoding='utf-8') as f:
    f.write(c)

print("✅ ALL PATCHES APPLIED")
